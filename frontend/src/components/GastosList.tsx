import { useState, useEffect } from 'react'
import Modal from './Modal'

interface Gasto {
  id: number;
  descricao: string;
  valor: number;
  data: string;
  tipo_pagamento: string;
  parcelas: number;
  cartao_id: number;
}

interface Cartao {
  id: number;
  nome: string;
  dono: string;
  data_fatura: number;
}

interface GastosListProps {
  apiUrl: string;
  activeProfile: string;
}

export default function GastosList({ apiUrl, activeProfile }: GastosListProps) {
  const [gastos, setGastos] = useState<Gasto[]>([])
  const [cartoes, setCartoes] = useState<Cartao[]>([])
  const [loading, setLoading] = useState(true)

  // Calendário
  const [mesAtual, setMesAtual] = useState(new Date().getMonth())
  const [anoAtual, setAnoAtual] = useState(new Date().getFullYear())

  // Modal de Parcelas
  const [gastoSelecionado, setGastoSelecionado] = useState<Gasto | null>(null)

  const formatMoney = (value: number) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value)

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr)
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '')
  }

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [gastosRes, cartoesRes] = await Promise.all([
          fetch(`${apiUrl}/gastos_diarios/`),
          fetch(`${apiUrl}/cartoes/`)
        ])
        const gastosData = await gastosRes.json()
        const cartoesData = await cartoesRes.json()
        setGastos(gastosData)
        setCartoes(cartoesData)
      } catch (err) {
        console.error('Erro ao buscar gastos:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [apiUrl])

  // Filtrar cartões do perfil ativo
  const cartoesDoPerfil = cartoes.filter(c => c.dono === activeProfile)
  const cartaoIds = new Set(cartoesDoPerfil.map(c => c.id))
  const cartaoNomes = Object.fromEntries(cartoesDoPerfil.map(c => [c.id, c.nome]))

  // Filtrar gastos por perfil e mês/ano
  const gastosFiltrados = gastos
    .filter(g => cartaoIds.has(g.cartao_id))
    .filter(g => {
      const d = new Date(g.data)
      return d.getMonth() === mesAtual && d.getFullYear() === anoAtual
    })
    .sort((a, b) => new Date(b.data).getTime() - new Date(a.data).getTime())

  const totalMes = gastosFiltrados.reduce((acc, g) => acc + g.valor, 0)

  // Calcular Projeção de Faturas (Crédito) para o mês selecionado
  const projecaoFatura = gastos.filter(g => cartaoIds.has(g.cartao_id) && g.tipo_pagamento.toLowerCase() === 'credito')
    .reduce((acc, g) => {
      const d = new Date(g.data)
      const cartao = cartoesDoPerfil.find(c => c.id === g.cartao_id)
      const diaFechamento = cartao?.data_fatura || 15
      
      // Mês da fatura em que esse gasto entra
      let mesFatura = d.getMonth()
      let anoFatura = d.getFullYear()
      if (d.getDate() > diaFechamento) {
        mesFatura += 1
        if (mesFatura > 11) {
          mesFatura = 0
          anoFatura += 1
        }
      }
      
      if (mesFatura === mesAtual && anoFatura === anoAtual) {
        return acc + g.valor
      }
      return acc
    }, 0)

  // Agrupar por dia
  const gastosPorDia: Record<string, Gasto[]> = {}
  for (const g of gastosFiltrados) {
    const dia = new Date(g.data).toLocaleDateString('pt-BR')
    if (!gastosPorDia[dia]) gastosPorDia[dia] = []
    gastosPorDia[dia].push(g)
  }

  // Navegação do calendário
  const irMesAnterior = () => {
    if (mesAtual === 0) { setMesAtual(11); setAnoAtual(a => a - 1) }
    else setMesAtual(m => m - 1)
  }
  const irProximoMes = () => {
    if (mesAtual === 11) { setMesAtual(0); setAnoAtual(a => a + 1) }
    else setMesAtual(m => m + 1)
  }
  const irHoje = () => {
    setMesAtual(new Date().getMonth())
    setAnoAtual(new Date().getFullYear())
  }

  const nomeMes = new Date(anoAtual, mesAtual).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })

  // Dias do mês para o mini calendário
  const primeiroDia = new Date(anoAtual, mesAtual, 1).getDay()
  const totalDias = new Date(anoAtual, mesAtual + 1, 0).getDate()

  // Dias que têm gastos
  const diasComGasto = new Set(
    gastosFiltrados.map(g => new Date(g.data).getDate())
  )

  const getTipoBadge = (tipo: string) => {
    switch (tipo.toLowerCase()) {
      case 'credito': return { label: 'Crédito', color: 'rgba(139, 92, 246, 0.25)', text: '#a78bfa' }
      case 'debito': return { label: 'Débito', color: 'rgba(59, 130, 246, 0.25)', text: '#93c5fd' }
      case 'pix': return { label: 'PIX', color: 'rgba(16, 185, 129, 0.25)', text: '#6ee7b7' }
      default: return { label: tipo, color: 'rgba(255,255,255,0.1)', text: '#fff' }
    }
  }

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Tem certeza que deseja apagar este gasto? O valor será estornado.')) return
    try {
      await fetch(`${apiUrl}/gastos_diarios/${id}`, { method: 'DELETE' })
      setGastos(prev => prev.filter(g => g.id !== id))
    } catch (err) {
      console.error('Erro ao deletar gasto:', err)
    }
  }

  // Lógica do modal de parcelas
  const getParcelasInfo = (gasto: Gasto) => {
    // Extrai o nome base removendo o padrão " (X/Y)" do final
    const match = gasto.descricao.match(/^(.+?)\s*\((\d+)\/(\d+)\)\s*$/)
    if (!match) return null

    const nomeBase = match[1].trim()
    const parcelaAtual = parseInt(match[2])
    const totalParcelas = parseInt(match[3])

    // Busca todas as parcelas relacionadas
    const parcelasRelacionadas = gastos
      .filter(g => {
        const m = g.descricao.match(/^(.+?)\s*\(\d+\/\d+\)\s*$/)
        return m && m[1].trim() === nomeBase && g.cartao_id === gasto.cartao_id
      })
      .sort((a, b) => {
        const ma = a.descricao.match(/\((\d+)\//)
        const mb = b.descricao.match(/\((\d+)\//)
        return (ma ? parseInt(ma[1]) : 0) - (mb ? parseInt(mb[1]) : 0)
      })

    // Calcula a data estimada da última parcela
    const dataInicio = new Date(parcelasRelacionadas[0]?.data || gasto.data)
    const dataFim = new Date(dataInicio)
    dataFim.setMonth(dataFim.getMonth() + totalParcelas - 1)

    return {
      nomeBase,
      parcelaAtual,
      totalParcelas,
      parcelasRelacionadas,
      valorParcela: gasto.valor,
      valorTotal: gasto.valor * totalParcelas,
      dataFim,
      parcelasPagas: parcelasRelacionadas.filter(p => {
        const dataParcela = new Date(p.data)
        return dataParcela <= new Date()
      }).length
    }
  }

  const handleClickGasto = (gasto: Gasto) => {
    if (gasto.tipo_pagamento.toLowerCase() === 'credito' && gasto.descricao.match(/\(\d+\/\d+\)/)) {
      setGastoSelecionado(gasto)
    }
  }

  const parcelasInfo = gastoSelecionado ? getParcelasInfo(gastoSelecionado) : null

  if (loading) return <p>Carregando gastos...</p>

  return (
    <div>
      {/* Calendário */}
      <div className="glass-panel calendario">
        <div className="calendario-header">
          <button className="cal-nav-btn" onClick={irMesAnterior}>‹</button>
          <div className="cal-titulo" onClick={irHoje}>
            <span className="cal-mes">{nomeMes}</span>
          </div>
          <button className="cal-nav-btn" onClick={irProximoMes}>›</button>
        </div>

        <div className="cal-weekdays">
          {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(d => (
            <span key={d} className="cal-weekday">{d}</span>
          ))}
        </div>

        <div className="cal-days">
          {/* Espaços vazios antes do primeiro dia */}
          {Array.from({ length: primeiroDia }).map((_, i) => (
            <span key={`empty-${i}`} className="cal-day empty" />
          ))}
          {/* Dias do mês */}
          {Array.from({ length: totalDias }).map((_, i) => {
            const dia = i + 1
            const hoje = new Date()
            const isHoje = dia === hoje.getDate() && mesAtual === hoje.getMonth() && anoAtual === hoje.getFullYear()
            return (
              <span
                key={dia}
                className={`cal-day ${isHoje ? 'hoje' : ''} ${diasComGasto.has(dia) ? 'com-gasto' : ''}`}
              >
                {dia}
                {diasComGasto.has(dia) && <span className="cal-dot" />}
              </span>
            )
          })}
        </div>
      </div>

      {/* Resumo do Mês */}
      <div className="dashboard-grid">
        <div className="glass-panel summary-box hover-lift transition-all" style={{ marginBottom: '1.5rem' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
            Gastos Totais ({nomeMes})
          </span>
          <span className="summary-value" style={{ color: 'var(--text-primary)' }}>
            {formatMoney(totalMes)}
          </span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            {gastosFiltrados.length} {gastosFiltrados.length === 1 ? 'lançamento' : 'lançamentos'} no mês civil
          </span>
        </div>

        <div className="glass-panel summary-box hover-lift transition-all" style={{ marginBottom: '1.5rem', borderLeft: '4px solid var(--accent-primary)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
            Projeção de Faturas ({nomeMes})
          </span>
          <span className="summary-value" style={{ color: 'var(--danger)' }}>
            {formatMoney(projecaoFatura)}
          </span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Soma dos cartões de crédito para este vencimento
          </span>
        </div>
      </div>

      {/* Lista de Gastos */}
      {gastosFiltrados.length === 0 ? (
        <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>Nenhum gasto encontrado neste mês.</p>
        </div>
      ) : (
        Object.entries(gastosPorDia).map(([dia, gastosNoDia]) => (
          <div key={dia} style={{ marginBottom: '1.5rem' }}>
            <h3 className="day-header">{dia}</h3>
            <div className="gastos-list">
              {gastosNoDia.map(gasto => {
                const badge = getTipoBadge(gasto.tipo_pagamento)
                const temParcela = gasto.tipo_pagamento.toLowerCase() === 'credito' && gasto.descricao.match(/\(\d+\/\d+\)/)
                return (
                  <div
                    key={gasto.id}
                    className={`gasto-item glass-panel transition-all ${temParcela ? 'clickable' : ''}`}
                    onClick={() => handleClickGasto(gasto)}
                  >
                    <div className="gasto-info">
                      <div className="gasto-main">
                        <span className="gasto-descricao">
                          {gasto.descricao}
                          {temParcela && <span className="parcela-icon"> 📊</span>}
                        </span>
                        <div className="gasto-tags">
                          <span className="gasto-badge" style={{ background: badge.color, color: badge.text }}>
                            {badge.label}
                          </span>
                          <span className="gasto-cartao">{cartaoNomes[gasto.cartao_id] || 'Cartão'}</span>
                        </div>
                      </div>
                      <div className="gasto-right">
                        <span className="gasto-valor">{formatMoney(gasto.valor)}</span>
                        <span className="gasto-data">{formatDate(gasto.data)}</span>
                        <button className="delete-btn" onClick={(e) => handleDelete(gasto.id, e)} title="Apagar gasto">
                          🗑
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))
      )}

      {/* Modal de Parcelas */}
      <Modal isOpen={!!gastoSelecionado} onClose={() => setGastoSelecionado(null)} title="Detalhes das Parcelas">
        {parcelasInfo && (
          <div className="parcelas-modal">
            <div className="parcelas-titulo">{parcelasInfo.nomeBase}</div>

            <div className="parcelas-resumo">
              <div className="parcela-stat">
                <span className="stat-label">Valor da Parcela</span>
                <span className="stat-value">{formatMoney(parcelasInfo.valorParcela)}</span>
              </div>
              <div className="parcela-stat">
                <span className="stat-label">Valor Total</span>
                <span className="stat-value">{formatMoney(parcelasInfo.valorTotal)}</span>
              </div>
            </div>

            {/* Barra de Progresso */}
            <div className="parcela-progresso">
              <div className="progresso-header">
                <span>{parcelasInfo.parcelasPagas} de {parcelasInfo.totalParcelas} parcelas</span>
                <span>{Math.round((parcelasInfo.parcelasPagas / parcelasInfo.totalParcelas) * 100)}%</span>
              </div>
              <div className="progresso-bar">
                <div
                  className="progresso-fill"
                  style={{ width: `${(parcelasInfo.parcelasPagas / parcelasInfo.totalParcelas) * 100}%` }}
                />
              </div>
              <span className="progresso-footer">
                Termina em {parcelasInfo.dataFim.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}
              </span>
            </div>

            {/* Timeline de Parcelas */}
            <div className="parcelas-timeline">
              {parcelasInfo.parcelasRelacionadas.map((p, i) => {
                const dataParcela = new Date(p.data)
                const isPaga = dataParcela <= new Date()
                return (
                  <div key={p.id} className={`timeline-item ${isPaga ? 'paga' : 'pendente'}`}>
                    <div className="timeline-dot" />
                    <div className="timeline-info">
                      <span className="timeline-label">
                        Parcela {i + 1}/{parcelasInfo.totalParcelas}
                      </span>
                      <span className="timeline-data">
                        {dataParcela.toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })}
                      </span>
                    </div>
                    <div className="timeline-valor">
                      <span>{formatMoney(p.valor)}</span>
                      <span className={`timeline-status ${isPaga ? 'paga' : 'pendente'}`}>
                        {isPaga ? '✓ Paga' : '⏳ Pendente'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
